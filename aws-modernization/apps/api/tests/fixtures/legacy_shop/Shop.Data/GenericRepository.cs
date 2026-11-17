using System.Data.Entity;
using System.Linq;

namespace Shop.Data
{
    public class GenericRepository<T> where T : class
    {
        protected DbSet<T> DBSet { get; set; }
        protected DbContext Context { get; set; }

        public GenericRepository(DbContext context)
        {
            this.Context = context;
            this.DBSet = context.Set<T>();
        }

        public virtual IQueryable<T> GetAll()
        {
            return this.DBSet;
        }

        public virtual T GetById(int id)
        {
            return this.DBSet.Find(id);
        }

        public virtual void Add(T entity)
        {
            this.DBSet.Add(entity);
        }

        public virtual void Update(T entity)
        {
            this.Context.Entry(entity).State = EntityState.Modified;
        }

        public virtual void Delete(T entity)
        {
            this.Context.Entry(entity).State = EntityState.Deleted;
        }

        public virtual void Delete(int id)
        {
            var entity = this.GetById(id);
            this.Delete(entity);
        }

        public virtual void Detach(T entity)
        {
            this.Context.Entry(entity).State = EntityState.Detached;
        }
    }
}
